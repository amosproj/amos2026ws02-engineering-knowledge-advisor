# Build the React frontend
FROM node:24-alpine AS build

WORKDIR /app

COPY apps/web/package*.json ./
RUN npm ci

COPY apps/web/ ./

# Passed from compose.yaml. VITE_* values are embedded in the JS bundle and readable
# in clear text by any client: never put secrets (passwords, API keys) here
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# Serve the production build with Nginx
FROM nginx:1.28-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY infra/nginx/default.conf /etc/nginx/conf.d/default.conf
