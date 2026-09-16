# Factuality Test Bot

[Factuality Test Bot](https://t.me/factuality_test_bot) is an interactive Telegram bot based on the book "Factfulness" by Hans Rosling, professor of international health and renowned TED speaker.

## What the bot does
- Runs a 13-question test
- Shows correct answers with explanations
- Helps reveal common misconceptions about the world


## Main Commands

```
/information  - Learn more about the bot
/language     - Choose the bot language
```

## Technologies
- 🐍 Python + Aiogram 3.x
- 📊 PostgreSQL + SQLAlchemy
- 🔄 Redis for state management

Docker Compose starts only the bot and its required PostgreSQL and Redis
services.


## About the book "Factfulness"

"Factfulness" is a book summarizing years of research by Hans Rosling, a professor of international health.
The author conducted fact-based tests among students, politicians, scientists, and even Nobel Prize laureates around the world.

Most participants - regardless of education or professional background - scored worse than if they had chosen answers at random.
Rosling illustrates this using an example with a chimpanzee choosing one of three bananas: on average, the chimp guessed 4 out of 13 answers correctly, while humans picked only 2–3 out of 13.

This highlights how even experts are subject to cognitive biases and stereotypes.

Hans Rosling explains key cognitive biases and instincts that make us distort reality, and provides advice on how to think more rationally.

The test is based on data collected by the author for the book.
Each question highlights widespread misconceptions about global trends such as poverty, education, and healthcare.


## Data relevance (UPD 2025)

The book and the test were created in 2015.
Some data has changed over 10 years:
- World population: 7 billion → 8.2 billion
- Access to electricity: ~80% → ~90%
- Extreme poverty: decreased almost threefold (28% → 9%)

However, the essence of the test remains fully relevant - it checks cognitive biases and instincts, not exact numbers. All long-term trends remain consistent.

After completing the test, the bot shows for each question: the correct answer, explanation, and updated 2025 data.


## Project author

The bot is developed as an open-source project to popularize the ideas of "Factfulness".


## License

MIT License
