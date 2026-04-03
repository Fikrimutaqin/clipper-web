from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from _database.db import get_db, User, SessionLocal
from core import create_access_token, settings, response_success
from passlib.context import CryptContext
import uuid
from pydantic import BaseModel, EmailStr, Field
from jose import JWTError, jwt
from google_auth import google_login_flow, new_state, read_oauth_state
from googleapiclient.discovery import build
from urllib.parse import urlparse

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=64)
    full_name: str = Field(..., min_length=2)
    role: str = "OWNER"

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    user_id: str

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user

def _safe_frontend_redirect(request: Request, redirect: str) -> str:
    origin = request.headers.get("origin") or ""
    referer = request.headers.get("referer") or ""
    referer_origin = ""
    if referer:
        try:
            rp = urlparse(referer)
            if rp.scheme and rp.netloc:
                referer_origin = f"{rp.scheme}://{rp.netloc}"
        except Exception:
            referer_origin = ""

    safe_redirect = "/login"
    if redirect.startswith("/"):
        return redirect
    try:
        parsed = urlparse(redirect)
        if parsed.scheme in {"http", "https"}:
            if origin and redirect.startswith(origin):
                safe_redirect = redirect
            elif referer_origin and redirect.startswith(referer_origin):
                safe_redirect = redirect
            elif parsed.netloc == "localhost:3000":
                safe_redirect = redirect
    except Exception:
        safe_redirect = "/login"
    return safe_redirect


@router.get("/google/connect")
async def google_connect(request: Request, redirect: str = "/login"):
    state = new_state()
    safe_redirect = _safe_frontend_redirect(request, redirect)

    payload = {"state": state, "redirect": safe_redirect, "purpose": "auth"}

    from core import serializer
    raw_state = serializer.dumps(payload)

    base_url = str(request.base_url).rstrip("/")
    redirect_uri = settings.google_redirect_uri or f"{base_url}/auth/google/callback"
    flow = google_login_flow(state=state, redirect_uri=redirect_uri)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    resp = RedirectResponse(url=auth_url, status_code=302)
    resp.set_cookie("oauth_state", raw_state, httponly=True, samesite="lax")
    return resp


async def handle_google_login_callback(request: Request, state: str = "", code: str = ""):
    payload = read_oauth_state(request)
    expected_state = payload.get("state")
    redirect_url = payload.get("redirect") or "/login"
    if not expected_state or not state or state != expected_state:
        raise HTTPException(status_code=400, detail="OAuth state tidak valid")
    if not code:
        raise HTTPException(status_code=400, detail="OAuth code tidak ditemukan")

    base_url = str(request.base_url).rstrip("/")
    redirect_uri = settings.google_redirect_uri or f"{base_url}/auth/google/callback"
    flow = google_login_flow(state=state, redirect_uri=redirect_uri)
    flow.fetch_token(code=code)
    creds = flow.credentials

    try:
        oauth2 = build("oauth2", "v2", credentials=creds)
        info = oauth2.userinfo().get().execute()
    except Exception:
        raise HTTPException(status_code=500, detail="Gagal mengambil data user dari Google")

    email = (info.get("email") or "").strip().lower()
    full_name = (info.get("name") or "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="Google account tidak memiliki email")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user_id = str(uuid.uuid4())
            random_password = uuid.uuid4().hex
            user = User(
                id=user_id,
                email=email,
                hashed_password=pwd_context.hash(random_password),
                full_name=full_name or email.split("@")[0],
                role="OWNER",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
    finally:
        db.close()

    access_token = create_access_token(data={"sub": user.id, "role": user.role})
    sep = "&" if "?" in redirect_url else "?"
    target = f"{redirect_url}{sep}token={access_token}"
    resp = RedirectResponse(url=target, status_code=302)
    resp.set_cookie("oauth_state", "", httponly=True, samesite="lax")
    return resp

@router.post("/register")
async def register(user_in: UserRegister, db: Session = Depends(get_db)):
    try:
        db_user = db.query(User).filter(User.email == user_in.email).first()
        if db_user:
            raise HTTPException(status_code=400, detail="Email sudah terdaftar")
        
        # Bcrypt hard limit check (72 bytes)
        # We limit to 64 bytes for safety and clear user feedback
        if len(user_in.password.encode('utf-8')) > 64:
            raise HTTPException(status_code=400, detail="Password terlalu panjang (maksimal 64 bytes)")
        
        user_id = str(uuid.uuid4())
        hashed_password = pwd_context.hash(user_in.password)
        
        new_user = User(
            id=user_id,
            email=user_in.email,
            hashed_password=hashed_password,
            full_name=user_in.full_name,
            role=user_in.role.upper()
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        access_token = create_access_token(data={"sub": user_id, "role": new_user.role})
        return response_success(
            message="Registrasi berhasil",
            data={
                "access_token": access_token, 
                "token_type": "bearer", 
                "role": new_user.role,
                "user_id": user_id
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"ERROR REGISTER: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Terjadi kesalahan pada server: {str(e)}"
        )

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    
    # Bcrypt hard limit check for login
    if len(form_data.password.encode('utf-8')) > 64:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email atau password salah",
        )

    if not user or not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email atau password salah",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.id, "role": user.role})
    return response_success(
        message="Login berhasil",
        data={
            "access_token": access_token, 
            "token_type": "bearer", 
            "role": user.role,
            "user_id": user.id
        }
    )

@router.get("/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    return response_success(
        message="Data user berhasil diambil",
        data={
            "id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "role": current_user.role
        }
    )
