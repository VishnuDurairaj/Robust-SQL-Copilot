FROM python:3.12

# Set the working directory
WORKDIR /app

RUN apt-get update && apt-get install -y unixodbc-dev

# Copy requirements and install Python dependencies (including Playwright)
COPY requirements.txt /app/

RUN pip install -r requirements.txt

# Copy the application and Jupyter configuration
COPY . /app

EXPOSE 8080

# Start Jupyter Notebook and Python application
CMD ["chainlit","run","assistant.py","--port","8080"]
