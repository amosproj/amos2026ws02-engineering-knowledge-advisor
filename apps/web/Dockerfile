ARG WEB_PROFILE=prod

FROM node:alpine AS web-base

WORKDIR /app

COPY apps/web/package*.json ./
RUN npm ci

COPY apps/web/ ./

FROM web-base AS dev

ARG WEB_PROFILE
RUN test "$WEB_PROFILE" = "dev"

EXPOSE 80
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "80"]

FROM web-base AS build

# Passed from compose.yaml. VITE_* values are embedded in the JS bundle and readable
# in clear text by any client: never put secrets (passwords, API keys) here
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

FROM nginx:alpine AS prod

ARG WEB_PROFILE
RUN test "$WEB_PROFILE" = "prod"

COPY --from=build /app/dist /usr/share/nginx/html
COPY infra/nginx/default.conf /etc/nginx/conf.d/default.conf
