import podonos

_PODONOS_API_BASE_URL = "https://dev.podonosapi.com"

def main():
    print(podonos.__version__)
    my_api_key = ""
    client = podonos.init(api_key=my_api_key, api_url=_PODONOS_API_BASE_URL)
    etor = client.create_evaluator()
    etor.add_file(path=f'./tr1.wav')
    etor.close()

def test_get_all_evaluations():
    api_key = ""
    client = podonos.init(api_key=api_key, api_url=_PODONOS_API_BASE_URL)
    evaluations = client.get_evaluation_list()
    print(evaluations)

if __name__ == '__main__':
    test_get_all_evaluations()
