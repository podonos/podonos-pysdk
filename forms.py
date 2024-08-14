import podonos
from podonos import File

client = podonos.init("OW7TZDUKNEJWNC5LE3TA", api_url="http://localhost:8000")

languages = [
    "en-us"
]  # , "en-gb", "en-au", "en-ca", "ko-kr", "zh-cn", "es-es", "es-mx", "fr-fr", "de-de", "it-it", "ja-jp", "pl-pl"]
etor = client.create_evaluator(
    name="Test: Speech Custom Query from SDK",
    desc="Test: Speech Custom Query from SDK",
    type="QMOS",
    lan="en-us",
    granularity=1,
)

etor.set_question("What do you think the quality of this speech")

for i in range(1, 6):
    etor.add_file(File(path="./tests/speech_two_ch1.wav", tags=["0"], script="two"))
    etor.add_file(File(path="./tests/speech_two_ch2.wav", tags=["2"], script="two"))

etor.close()

# uuids = [
#     '72d0ae6b-ab44-47ec-824b-1b4d35e4f5a4',
#     'e3f0a0c9-8bf6-47e9-9def-5a9fee05d0cb',
#     '829d1bd9-6ebc-4183-a0b4-2c6ee7b43425',
#     'd39c41f5-fbee-4de6-9dcd-ce5e810f6bb0',
#     'aab76c59-a5fe-451c-a9bd-a5693b8209e2',
#     'b1841682-d736-4d11-b062-1703e621d359',
#     '34fd59c1-45cb-49dd-9285-897bed4a4679',
#     '2a7ebfd6-d4b6-4c79-9ac0-c5327c2cb1e8',
#     'c5f41629-6901-49b5-a358-18e8c267a400',
#     'f03e8fd1-727f-4985-9b62-6728c134da77',
#     '27e1b086-4652-4701-8fd7-8ddbe5458c54',
#     '4cf1e49f-b31d-4d1e-bc6c-ed5505317dde',
#     '012dc72b-fc13-4793-bfb8-e220e6e4d0ff',
#     '08608768-9c73-40e8-8a05-8262eb9b083c',
#     'b42f4937-1cfd-45e5-96b4-4cc6d28801a7',
#     '0391f127-cdba-45e8-b7a8-abf5d8029797',
#     '43f748d6-a544-4a5f-965a-b413254ed436'
# ]


# for uuid in uuids:
#     client.download_stats_csv_by_id(uuid, f"{uuid}.csv")

# # aws_male = ["Matthew", "Joey", "Justin"]
# # aws_female = ["Joanna", "Kendra", "Salli"]
# # tts_maker_male = ["alfie", "christ", "miles"]
# # tts_maker_female = ["alayna", "elizabeth", "chloe"]
# # openai_male = ["echo", "fable", "onyx"]
# # openai_female = ["alloy", "nova", "shimmer"]

# # aws_files = os.listdir("./aws")
# # tts_maker_files = os.listdir("./tts-maker")
# # openai_files = os.listdir("./openai")

# # for lan in languages:
# #     etor = client.create_evaluator(
# #         name=f"OpenAI vs AWS Polly's Preference",
# #         desc=f"OpenAI vs AWS Polly's Preference",
# #         type="PREF",
# #         lan=lan,
# #         granularity=1,
# #         num_eval=30
# #     )

# #     for i in range(1, 21):
# #         aws_file = [file for file in aws_files if file.startswith(f"output_{i}_")][0]
# #         openai_file = [file for file in openai_files if file.startswith(f"output_{i}_")][0]

# #         aws_tags = []
# #         aws_file_name = aws_file.split(".")[0]
# #         if aws_file_name.split("_")[2] in aws_male:
# #             aws_tags = ["AWS", "Male", f"Sentence_{i}"]
# #         else:
# #             aws_tags = ["AWS", "Female", f"Sentence_{i}"]

# #         openai_tags = []
# #         openai_file_name = openai_file.split(".")[0]
# #         if openai_file_name.split("_")[2] in openai_male:
# #             openai_tags = ["OpenAI", "Male", f"Sentence_{i}"]
# #         else:
# #             openai_tags = ["OpenAI", "Female", f"Sentence_{i}"]

# #         etor.add_file_set(
# #             File(path=f'aws/{aws_file}', tags=aws_tags),
# #             File(path=f'openai/{openai_file}', tags=openai_tags)
# #         )
# #     etor.close()
