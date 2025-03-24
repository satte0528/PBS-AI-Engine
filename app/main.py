from fastapi import FastAPI
from app.routers import match


app = FastAPI(title="ML Resume Matcher API")


app.include_router(match.router)


@app.get("/")
async def root():
    return {"message": "Welcome to the ML Resume Matcher API"}
