import podonos
import requests

_PODONOS_API_BASE_URL = "https://dev.podonosapi.com"


def main():
    print(podonos.__version__)
    my_api_key = ""
    client = podonos.init(api_key=my_api_key)
    etor = client.create_evaluator()
    etor.add_file(path=f'/home/soohyun/project/pysdk/speech_0.mp3')
    etor.close()


if __name__ == '__main__':
    main()
