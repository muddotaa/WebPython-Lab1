from datetime import date

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from database import Base, engine, get_db
from models import Author, Book, Loan, User

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Library RESTful API",
    description="""
    Лабораторна робота №1.

    RESTful API вебзастосунок для керування бібліотекою.

    Ролі:
    - admin: створення, читання, оновлення, видалення книг;
    - user: перегляд книг і створення позик.
    """,
    version="1.0.0",
    contact={
        "name": "Student",
        "email": "student@example.com"
    },
    openapi_tags=[
        {
            "name": "pages",
            "description": "HTML-сторінки, які генеруються на сервері"
        },
        {
            "name": "books",
            "description": "CRUD-операції для сутності Book"
        },
        {
            "name": "loans",
            "description": "Операції користувача для позики книг"
        }
    ]
)

templates = Jinja2Templates(directory="templates")


def get_or_create_author(db: Session, full_name: str, country: str = "") -> Author:
    full_name = full_name.strip()
    country = country.strip() or "-"

    author = db.query(Author).filter(Author.full_name == full_name).first()
    if author:
        if country != "-":
            author.country = country
        return author

    author = Author(full_name=full_name, country=country)
    db.add(author)
    db.flush()
    return author


def seed_data(db: Session) -> None:
    existing_user = db.query(User).first()
    if existing_user:
        return

    admin = User(username="admin", role="admin")
    user = User(username="user", role="user")

    author1 = Author(full_name="Леся Українка", country="Україна")
    author2 = Author(full_name="Джордж Орвелл", country="Велика Британія")
    author3 = Author(full_name="Айзек Азімов", country="США")

    book1 = Book(
        title="Лісова пісня",
        genre="Драма-феєрія",
        year=1911,
        available=True,
        author=author1
    )
    book2 = Book(
        title="1984",
        genre="Антиутопія",
        year=1949,
        available=True,
        author=author2
    )
    book3 = Book(
        title="Фундація",
        genre="Наукова фантастика",
        year=1951,
        available=True,
        author=author3
    )

    db.add_all([admin, user, author1, author2, author3, book1, book2, book3])
    db.commit()


@app.on_event("startup")
def on_startup() -> None:
    db = next(get_db())
    seed_data(db)
    db.close()


def require_admin(role: str) -> None:
    if role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Ця дія доступна тільки адміністратору"
        )


@app.get("/", response_class=HTMLResponse, tags=["pages"])
def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )


@app.get("/books", response_class=HTMLResponse, tags=["books"])
def read_books(
    request: Request,
    role: str = "user",
    db: Session = Depends(get_db)
):
    books = (
        db.query(Book)
        .options(joinedload(Book.author))
        .order_by(Book.id)
        .all()
    )
    authors = db.query(Author).order_by(Author.full_name).all()

    return templates.TemplateResponse(
        "books.html",
        {
            "request": request,
            "books": books,
            "authors": authors,
            "role": role
        }
    )


@app.post("/books/create", tags=["books"])
def create_book(
    title: str = Form(...),
    genre: str = Form(...),
    year: int = Form(...),
    author_name: str = Form(...),
    author_country: str = Form(""),
    role: str = Form("user"),
    db: Session = Depends(get_db)
):
    require_admin(role)

    author = get_or_create_author(db, author_name, author_country)

    book = Book(
        title=title,
        genre=genre,
        year=year,
        author_id=author.id,
        available=True
    )
    db.add(book)
    db.commit()

    return RedirectResponse(
        url=f"/books?role={role}",
        status_code=303
    )


@app.get("/books/{book_id}/edit", response_class=HTMLResponse, tags=["books"])
def edit_book_page(
    book_id: int,
    request: Request,
    role: str = "user",
    db: Session = Depends(get_db)
):
    require_admin(role)

    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Книгу не знайдено")

    authors = db.query(Author).order_by(Author.full_name).all()

    return templates.TemplateResponse(
        "edit_book.html",
        {
            "request": request,
            "book": book,
            "authors": authors,
            "role": role
        }
    )


@app.post("/books/{book_id}/update", tags=["books"])
def update_book(
    book_id: int,
    title: str = Form(...),
    genre: str = Form(...),
    year: int = Form(...),
    author_name: str = Form(...),
    author_country: str = Form(""),
    available: bool = Form(False),
    role: str = Form("user"),
    db: Session = Depends(get_db)
):
    require_admin(role)

    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Книгу не знайдено")

    author = get_or_create_author(db, author_name, author_country)

    book.title = title
    book.genre = genre
    book.year = year
    book.author_id = author.id
    book.available = available

    db.commit()

    return RedirectResponse(
        url=f"/books?role={role}",
        status_code=303
    )


@app.post("/books/{book_id}/delete", tags=["books"])
def delete_book(
    book_id: int,
    role: str = Form("user"),
    db: Session = Depends(get_db)
):
    require_admin(role)

    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Книгу не знайдено")

    db.delete(book)
    db.commit()

    return RedirectResponse(
        url=f"/books?role={role}",
        status_code=303
    )


@app.post("/loans/create", tags=["loans"])
def create_loan(
    book_id: int = Form(...),
    role: str = Form("user"),
    db: Session = Depends(get_db)
):
    if role != "user":
        raise HTTPException(
            status_code=403,
            detail="Позики може створювати тільки користувач"
        )

    user = db.query(User).filter(User.role == "user").first()
    book = db.query(Book).filter(Book.id == book_id).first()

    if not book:
        raise HTTPException(status_code=404, detail="Книгу не знайдено")

    if not book.available:
        raise HTTPException(status_code=400, detail="Книга вже видана")

    loan = Loan(
        user_id=user.id,
        book_id=book.id,
        loan_date=date.today().isoformat()
    )
    book.available = False

    db.add(loan)
    db.commit()

    return RedirectResponse(
        url=f"/books?role={role}",
        status_code=303
    )


@app.post("/loans/{loan_id}/return", tags=["loans"])
def return_loan(
    loan_id: int,
    role: str = Form("user"),
    db: Session = Depends(get_db)
):
    if role != "user":
        raise HTTPException(
            status_code=403
        )

    loan = (
        db.query(Loan)
        .options(joinedload(Loan.book))
        .filter(Loan.id == loan_id)
        .first()
    )
    if not loan:
        raise HTTPException(status_code=404)

    loan.book.available = True
    db.delete(loan)
    db.commit()

    return RedirectResponse(
        url=f"/loans?role={role}",
        status_code=303
    )


@app.get("/loans", response_class=HTMLResponse, tags=["loans"])
def read_loans(
    request: Request,
    role: str = "user",
    db: Session = Depends(get_db)
):
    loans = (
        db.query(Loan)
        .options(joinedload(Loan.user), joinedload(Loan.book))
        .order_by(Loan.id.desc())
        .all()
    )

    return templates.TemplateResponse(
        "loans.html",
        {
            "request": request,
            "loans": loans,
            "role": role
        }
    )
