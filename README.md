# Web Media Converter

A web app that converts media files into different formats.

This is a copy of my submission for the NCEA Level 3 Digital Technology achievement standard 3.8 Complex Process, better adapted for self hosting. You can find the old repo here: https://github.com/0scar-M/3.8-complex-processes

Images: [DockerHub Repo](https://hub.docker.com/repository/docker/0scarm/web-media-converter/general)

## ```docker-compose.yml``` file for hosting application
```yml
services:
  frontend:
    image: 0scarm/web-media-converter:frontend
    ports:
      - "3000:80"
    environment:
      - BACKEND_URL=http://localhost:5000
    depends_on:
      - backend
    restart: unless-stopped

  backend:
    image: 0scarm/web-media-converter:backend
    volumes:
      - db_volume:/data
    ports:
      - "5000:5000"
    environment:
      - DATABASE_PATH=/data/database.db
    depends_on:
      - database
    restart: unless-stopped
  
  database:
    image: 0scarm/web-media-converter:database
    volumes:
      - db_volume:/data
    restart: unless-stopped

volumes:
  db_volume:
```
