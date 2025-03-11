FROM python:3.12.4-slim

# Install ffmpeg
RUN apt-get -y update && \ 
    apt-get -y upgrade && \
    apt-get install -y ffmpeg

WORKDIR /app

COPY requirements.txt /app/

RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

EXPOSE 5000

CMD ["uvicorn", "main:app", "--host=0.0.0.0", "--port=5000"]
