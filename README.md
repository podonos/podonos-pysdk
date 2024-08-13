# Podonos

## Quick Start

### 👨‍💻 1. Get an API key
Visit [https://www.podonos.com](https://www.podonos.com), log in or sign up, and get an API key.
For more details, see [Docs](https://www.podonos.com/docs/apikey)

### 💾 2. Install podonos Python package
First of all, make sure you have installed Python 3.8 or newer

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
from podonos import *

client = podonos.init(api_key="<YOUR_API_KEY_HERE>")
etor = client.create_evaluator()
for i in script_list:
  gen_audio = my_model.generate_and_save(i, script_list[i], f'/a/b/{i}.wav')
  etor.add_file(file=File(path=f'/a/b/{i}.wav', tags=["syn1"]))
etor.close()
```
Once we evaluate the audio files, we will email you the evaluation report within 12 hours.

## 👌 How to run the code testing

Run this at the base directory:
```bash
python -m unittest
```

## 📗 Documentation

For a deeper dive on all capabilities and details, please refer to [Documentation](https://www.podonos.com/docs).

## 📑 License
[MIT License](https://github.com/podonos/pysdk/blob/main/LICENSE)