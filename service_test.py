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

def test_get_stimulus_stats_by_id():
    api_key = ""
    client = podonos.init(api_key=api_key, api_url=_PODONOS_API_BASE_URL)
    evaluations = client.get_evaluation_list()
    for evaluation in evaluations:
        stats = client.get_stimulus_stats_by_id(evaluation.id)
        print(stats)

def test_get_stimulus_stats_csv_by_id():
    api_key = ""
    client = podonos.init(api_key=api_key, api_url=_PODONOS_API_BASE_URL)
    evaluations = client.get_evaluation_list()
    for evaluation in evaluations:
        client.download_stimulu_stats_csv_by_id(evaluation.id, './eval_stats.csv')

if __name__ == '__main__':
    main()
