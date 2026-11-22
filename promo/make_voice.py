import asyncio, json, edge_tts

TEXT = (
    "Хватит сливать деньги на платные API! "
    "Я сделал мост, который высасывает токены прямо из обычного веб-чата Gemini и DeepSeek "
    "и даёт нейросети полный контроль над Windows. "
    "Она сама пишет код, запускает программы и чинит свои же ошибки в реальном времени — "
    "абсолютно бесплатно, без ключей и лимитов. "
    "Весь исходный код уже открыт на моём GitHub — забирай по ссылке в шапке профиля!"
)

async def main():
    communicate = edge_tts.Communicate(TEXT, voice="ru-RU-DmitryNeural", rate="+18%", pitch="+2Hz")
    words = []
    with open(r"C:\Users\Максим\Desktop\ai_bridge\promo\voice.mp3", "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({
                    "text": chunk["text"],
                    "start": chunk["offset"] / 10_000_000,
                    "end": (chunk["offset"] + chunk["duration"]) / 10_000_000
                })
    with open(r"C:\Users\Максим\Desktop\ai_bridge\promo\timings.json", "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=2)
    print(f"VOICE_OK: {len(words)} words, total {words[-1]['end'] if words else 0:.2f}s")

asyncio.run(main())
