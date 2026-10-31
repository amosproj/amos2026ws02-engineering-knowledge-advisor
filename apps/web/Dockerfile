FROM node:24.22.1-alpine AS deps

WORKDIR /app

COPY apps/web/package*.json ./
RUN npm ci

# Listens on port 80, like Nginx in the prod stage, so both share one port mapping
FROM deps AS dev

COPY apps/web/ ./

EXPOSE 80

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "80", "--strictPort"]

# Build the React frontend
FROM deps AS build

COPY apps/web/ ./

# Passed from compose.yaml. VITE_* values are embedded in the JS bundle and readable
# in clear text by any client: never put secrets (passwords, API keys) here
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# Serve the production build with Nginx
FROM nginx:1.28-alpine AS prod

COPY --from=build /app/dist /usr/share/nginx/html
COPY infra/nginx/default.conf /etc/nginx/conf.d/default.conf
