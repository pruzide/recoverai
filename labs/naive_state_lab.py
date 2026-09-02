import os

import uvicorn
from fastapi import FastAPI


app = FastAPI(title="Naive In-Memory State Lab")

processed_events = set()
processed_count = 0


@app.post("/naive/event/{event_id}")
def receive_event(event_id: str):
    global processed_count

    if event_id not in processed_events:
        processed_events.add(event_id)
        processed_count += 1

        return {
            "event_id": event_id,
            "processed": True,
            "local_count": processed_count,
        }

    return {
        "event_id": event_id,
        "processed": False,
        "local_count": processed_count,
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8001"))
    uvicorn.run(app, host="127.0.0.1", port=port)