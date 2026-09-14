FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json .npmrc ./
RUN npm ci --no-audit --no-fund
COPY index.html vite.config.mjs ./
COPY src ./src
COPY public ./public
COPY scripts ./scripts
COPY worker ./worker
COPY .openai ./.openai
COPY tests/sites-worker.test.mjs ./tests/sites-worker.test.mjs
RUN npm run build && npm run test:sites

FROM nginx:alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/client /usr/share/nginx/html
EXPOSE 80
