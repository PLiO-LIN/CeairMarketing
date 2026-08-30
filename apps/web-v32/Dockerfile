FROM nginx:1.28-alpine
RUN apk add --no-cache apache2-utils
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html styles.css ui-premium.css ui-production-v2.css app.js v31.js data.js v32.js production.js market-hotspots.js /usr/share/nginx/html/
COPY brand /usr/share/nginx/html/brand
COPY docker-entrypoint-auth.sh /docker-entrypoint.d/20-auth.sh
RUN chmod +x /docker-entrypoint.d/20-auth.sh
EXPOSE 80
