FROM httpd:alpine

COPY . /usr/local/apache2/htdocs/

COPY ./entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
CMD ["/entrypoint.sh"]

EXPOSE 80
