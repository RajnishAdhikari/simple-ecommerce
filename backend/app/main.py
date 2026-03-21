from fastapi import FastAPI

app = FastAPI()

# Import routes
from .routes import user, product, order

app.include_router(user.router)
app.include_router(product.router)
app.include_router(order.router)