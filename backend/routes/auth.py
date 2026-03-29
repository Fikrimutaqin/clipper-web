from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from db import get_db, User
from core import create_access_token, settings, response_success
from passlib.context import CryptContext
import uuid
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from jose import JWTError, jwt

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
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user

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
