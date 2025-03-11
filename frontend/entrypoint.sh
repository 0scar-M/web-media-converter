#!/bin/sh

# Inject BACKEND_URL into config.js
echo "window.env = { BACKEND_URL: \"${BACKEND_URL}\" };" > /usr/local/apache2/htdocs/config.js

# Start Apache in the foreground
httpd-foreground
