FROM nginx:1.28-alpine
RUN apk add --no-cache apache2-utils
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY dist /usr/share/nginx/html
COPY docker-entrypoint-auth.sh /docker-entrypoint.d/20-auth.sh
RUN chmod +x /docker-entrypoint.d/20-auth.sh
EXPOSE 80
