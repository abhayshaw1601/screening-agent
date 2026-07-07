from fastapi import FastAPI

app = FastAPI(title="PG AGI Screener API")

@app.get("/")
def read_root():
    return {"message": "Welcome to PG AGI Screener API"}
