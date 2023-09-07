branch=`git rev-parse --abbrev-ref HEAD`
docker build -t rbrandstaedter/solarflow-topic-mapper:$branch .

docker image push rbrandstaedter/solarflow-topic-mapper:$branch