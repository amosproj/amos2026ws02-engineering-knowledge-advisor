# Build the React frontend
FROM node:24.22.0-alpine AS build

WORKDIR /app

COPY apps/web/package*.json ./
RUN npm ci

COPY apps/web/ ./
RUN npm run build

# Serve the production build with Nginx
FROM nginx:1.28-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY infra/nginx/default.conf /etc/nginx/conf.d/default.conf