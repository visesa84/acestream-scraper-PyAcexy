# Use the official Python image from the Docker Hub
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Create the config directory
RUN mkdir -p /app/config

# Install wget, curl, and other dependencies
RUN apt-get update && apt-get install -y wget curl gnupg

# Install Firefox and GeckoDriver
RUN apt-get update && \
    apt-get install -y firefox-esr && \
    wget -O /tmp/geckodriver.tar.gz https://github.com/mozilla/geckodriver/releases/download/v0.35.0/geckodriver-v0.35.0-linux64.tar.gz && \
    tar -xzf /tmp/geckodriver.tar.gz -C /usr/local/bin && \
    rm /tmp/geckodriver.tar.gz

# Make GeckoDriver executable
RUN chmod +x /usr/local/bin/geckodriver

# Copy the requirements file and app code to the working directory
COPY requirements.txt requirements.txt
COPY wsgi.py wsgi.py
COPY app/ app/
COPY entrypoint.sh entrypoint.sh

# Install the required dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Gunicorn
RUN pip install gunicorn

# Install Selenium
RUN pip install selenium

# Install ZeroNet dependencies
RUN pip install msgpack-python gevent

# Download and install ZeroNet
RUN wget https://github.com/HelloZeroNet/ZeroNet-linux/archive/dist-linux64/ZeroNet-py3-linux64.tar.gz
RUN tar xvpfz ZeroNet-py3-linux64.tar.gz
RUN mv ZeroNet-linux-dist-linux64 ZeroNet

# Set environment variable to indicate Docker environment
ENV DOCKER_ENV=true

# Expose the port Gunicorn will run on
EXPOSE 8000

# Expose the ZeroNet port
EXPOSE 43110

# Set the entrypoint script as executable
RUN chmod +x entrypoint.sh

# Set the entrypoint script
ENTRYPOINT ["./entrypoint.sh"]
