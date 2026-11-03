from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Author, Genre, User, utcnow
from ..schemas import OnboardingIn, Preferences, TasteOut, UserOut, UserUpdate
from ..services import find_existing_names
from ..taste import build_taste
from .auth import _user_out

router = APIRouter(prefix="/users", tags=["Profile & Preferences"])


@router.get("/me", response_model=UserOut, summary="Get my profile")
def me(user: User = Depends(get_current_user)):
    return _user_out(user)


@router.put("/me", response_model=UserOut, summary="Manage profile")
def update_me(data: UserUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for field, value in data.model_dump(exclude_unset=True).items():
        if field in ("name", "role") and value is None:
            continue  # NOT NULL columns: an explicit null means "leave unchanged"
        if field == "role" and user.role == "admin":
            continue  # never demote an admin through the profile endpoint
        setattr(user, field, value)
    db.commit()
    return _user_out(user)


@router.put("/me/preferences", response_model=UserOut, summary="Update preferences (favourite genres / authors)")
def update_preferences(data: Preferences, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # users may only pick genres / authors that exist in the catalogue (they cannot create catalogue rows)
    user.favorite_genres = find_existing_names(db, Genre, data.favorite_genres)
    user.favorite_authors = find_existing_names(db, Author, data.favorite_authors)
    db.commit()
    return _user_out(user)


@router.post("/me/onboarding", response_model=UserOut, summary="Finish (or skip) first-run onboarding: genres + moods")
def finish_onboarding(data: OnboardingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if data.favorite_genres:
        user.favorite_genres = find_existing_names(db, Genre, data.favorite_genres)
    user.favorite_moods = data.favorite_moods
    user.onboarded_at = utcnow()
    db.commit()
    return _user_out(user)


@router.get("/me/taste", response_model=TasteOut, summary="My taste profile (genres, authors, moods, DNA sentence)")
def my_taste(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return build_taste(db, user)
