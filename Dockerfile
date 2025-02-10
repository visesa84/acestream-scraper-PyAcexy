# Use the official Python image from the Docker Hub
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Create the config directory
RUN mkdir -p /app/config

# Copy the requirements file and app code to the working directory
COPY requirements.txt requirements.txt
COPY wsgi.py wsgi.py
COPY app/ app/
COPY entrypoint.sh entrypoint.sh

# Install the required dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Gunicorn
RUN pip install gunicorn

# Install ZeroNet dependencies
RUN pip install msgpack-python gevent

# Download and install ZeroNet
RUN wget https://github.com/HelloZeroNet/ZeroNet/archive/master.tar.gz
RUN tar xvpfz master.tar.gz

# Set environment variable to indicate Docker environment
ENV DOCKER_ENV=true

# Expose the port Gunicorn will run on
EXPOSE 8000

# Set the entrypoint script
ENTRYPOINT ["./entrypoint.sh"]
