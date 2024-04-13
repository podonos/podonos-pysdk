import boto3
import podonos

def synthesize_audio():
    polly_client = boto3.Session(
        aws_access_key_id='',
        aws_secret_access_key='',
        region_name='eu-west-2').client('polly')

    # Scripts from LibreSpeech
    script = "The two doctors therefore entered the room"
    index = 0
    response = polly_client.synthesize_speech(
        VoiceId='Brian',
        OutputFormat='mp3',
        Text='The two doctors therefore entered the room',
        Engine='neural')

def main():
    file = open(f'speech_{index}.mp3', 'wb')
    index += 1
    file.write(response['AudioStream'].read())
    file.close()


if __name__ == '__main__':
    main()
