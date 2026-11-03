FROM node:26-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_ENABLE_LOCAL_LEAGUE=false
ENV VITE_ENABLE_LOCAL_LEAGUE=${VITE_ENABLE_LOCAL_LEAGUE}
# Use the same-origin /api proxy; never copy a developer's frontend .env.
RUN npm run build

FROM nginx:stable-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
