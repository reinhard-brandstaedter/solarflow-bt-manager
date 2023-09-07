FROM python:3.10-alpine

# Create stdconfig directory
WORKDIR /

COPY solarflow-topic-mapper.py /

RUN pip install paho-mqtt
ENTRYPOINT ["python","solarflow-topic-mapper.py"]