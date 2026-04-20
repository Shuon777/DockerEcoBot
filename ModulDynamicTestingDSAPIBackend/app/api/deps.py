from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

# Используем схему Bearer (заголовок Authorization: Bearer <token>)
reusable_oauth2 = HTTPBearer()

def validate_token(http_auth: HTTPAuthorizationCredentials = Security(reusable_oauth2)):
    """
    Проверяет валидность токена в заголовках запроса.
    """
    if http_auth.credentials != settings.API_AUTH_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный или отсутствующий API токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return http_auth.credentials