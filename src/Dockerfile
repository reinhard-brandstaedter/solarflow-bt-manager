FROM rbrandstaedter/solarflow-control-baseimage:latest

# Create stdconfig directory
WORKDIR /

COPY solarflow-topic-mapper.py /

#RUN pip install paho-mqtt
# FIX: Erzwinge die moderne Version 2.x, die das Skript für 'CallbackAPIVersion' braucht
RUN pip install --no-cache-dir "paho-mqtt>=2.0.0"

ENTRYPOINT ["python","solarflow-topic-mapper.py"]
