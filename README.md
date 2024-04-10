# Podonos

## Quick Start

### 👨‍💻 1. Get an API key
Visit [https://www.podonos.com](https://www.podonos.com), log in or sign up, and get an API key.

### 💾 2. Installa podonos Python package
First of all, make sure you have installed Python 3.6.6 or newer

```bash
python --version
```

Once you confirm your Python version, install the package:

```bash
pip install podonos
```

### 🎙️ 3. Start speech evaluation
```python
import podonos

client = podonos.init(api_key="<YOUR_API_KEY_HERE>")
etor = client.create_evaluator()
for i in script_list:
  gen_audio = my_model.generate_and_save(i, script_list[i], f'/a/b/{i}.wav')
  etor.add_file(f'/a/b/{i}.wav')
etor.close()
```
Once we evaluate the audio files, we will email you the evaluation report within 12 hours.

## 📗 Documentation

For a deeper dive on all capabilities and details, please refer to [Documentation](https://podonos.mintlify.app/).

## 📑 License
[MIT License](https://github.com/podonos/pysdk/blob/main/LICENSE)