FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

COPY . .

ENV PORT=10000
EXPOSE 10000

CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]