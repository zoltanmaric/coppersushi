# The forecast at eleven

A Copper Sushi video lesson on reconstructing the day-ahead price forecast a trader could retrieve at 11:00. Run the exercise in this directory with Python 3.10 or later.

```sh
python replay.py 11:00
python replay.py 11:20
```

Both queries target tomorrow’s 18:00–18:15 delivery quarter. Kpler describes the morning update times. The two prices and the wind receipt time illustrate the cutoff rule. [Kpler methodology](https://help.kpler.com/en/articles/8925114-short-term-power-forecasts-methodology)

The bar chart compares Eiser’s 11:00 and noon editions over 672 DE–LU quarters. It shows our recomputation of weighted interval score against SMARD truth. The noon edition used a different model and could see early auction results. [Paired-week calculation, dates and underlying data](../../wiki/price-forecasting/energy-arena-benchmarks.md#paired-week)

This manual replay is an exercise for Google’s level 0. The same eligibility rule can serve training and live issuing as the pipeline is automated. [Google Cloud MLOps levels](https://docs.cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning) · [Forecasting design guide](../../wiki/forecasting-system-design.md)

## Render

Install Pillow 10.1 or later and the FFmpeg tools (ffmpeg and ffprobe). Export an ElevenLabs API key as ELEVENLABS_API_KEY in your shell, then run:

```sh
python voice.py
python render.py --scene 2
python render.py
```

The voice step synthesizes the six paragraphs in narration.txt and saves character timings. It reuses local clips for unchanged paragraphs. The renderer aligns visual reveals to spoken phrases. The completed film is build/the-1100-forecast.mp4. Audio, timings and renders stay in the ignored build directory. Regenerating narration can change its delivery and duration.
