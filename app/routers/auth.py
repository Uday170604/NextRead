from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Genre, User
from ..schemas import Token, UserCreate, UserOut
from ..security import create_access_token, hash_password, verify_password
from ..services import find_existing_names

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED, summary="Sign up")
def register(data: UserCreate, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == data.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(
        name=data.name.strip(), email=data.email, password_hash=hash_password(data.password), role=data.role,
        date_of_birth=data.date_of_birth, street=data.street, city=data.city, state=data.state,
    )
    user.favorite_genres = find_existing_names(db, Genre, data.favorite_genres)
    db.add(user)
    db.commit()
    return _user_out(user)


@router.post("/login", response_model=Token, summary="Log in (OAuth2 password flow; username = email)")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == form.username.strip().lower()))
    if not user or not user.is_active or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password",
                            headers={"WWW-Authenticate": "Bearer"})
    return Token(access_token=create_access_token(user.id, user.role), user=_user_out(user))


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id, name=user.name, email=user.email, role=user.role, date_of_birth=user.date_of_birth, age=user.age,
        street=user.street, city=user.city, state=user.state, created_at=user.created_at,
        favorite_genres=[g.name for g in user.favorite_genres], favorite_authors=[a.name for a in user.favorite_authors],
        favorite_moods=list(user.favorite_moods or []), onboarded=user.onboarded_at is not None,
    )
