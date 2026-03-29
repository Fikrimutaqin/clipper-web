FROM node:18-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

# Next.js collects completely anonymous telemetry data about general usage.
# Learn more here: https://nextjs.org/telemetry
ENV NEXT_TELEMETRY_DISABLED 1

# If you are using the App Router, Next.js will build the application on startup in dev mode
# CMD ["npm", "run", "dev"]
# For production:
# RUN npm run build
# CMD ["npm", "run", "start"]

CMD ["npm", "run", "dev"]
