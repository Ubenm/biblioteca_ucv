FROM python:3.9
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y wait-for-it
COPY . .
CMD ["sh", "-c", "wait-for-it db:3306 --timeout=30 -- python app.py"]