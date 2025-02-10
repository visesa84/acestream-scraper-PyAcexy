# Use the official Python image from the Docker Hub
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Create the config directory
RUN mkdir -p /app/config

# Install wget, curl, and other dependencies
RUN apt-get update && apt-get install -y wget curl gnupg

# Install Chrome
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -
RUN sh -c 'echo "deb [arch=amd64] https://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
RUN apt-get update && apt-get install -y google-chrome-stable

# Install chromedriver
RUN apt-get install -yqq unzip
RUN CHROMEDRIVER_VERSION=`curl -sS chromedriver.storage.googleapis.com/LATEST_RELEASE` && \
    wget -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip && \
    unzip /tmp/chromedriver.zip -d /usr/local/bin/

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
