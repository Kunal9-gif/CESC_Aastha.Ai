import speech_recognition as sr
import os

def audio_to_text(file_path):
    # Check if file exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File '{file_path}' not found.")

    recognizer = sr.Recognizer()

    with sr.AudioFile(file_path) as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        audio = recognizer.record(source)

    try:
        text = recognizer.recognize_google(audio)
        return text

    except sr.UnknownValueError:
        raise ValueError("Could not understand the audio. Try a clearer recording.")
    except sr.RequestError as e:
        raise ConnectionError(f"API request failed: {e}")


if __name__ == "__main__":
    audio_file = input("Enter the path to your audio file: ").strip()

    try:
        result = audio_to_text(audio_file)
        print(result)
    except Exception as e:
        print(f"Error: {e}")