"""
Demo data for NextRead: a catalogue of well-known books (short original descriptions), seven persona users that
match the project documentation, and ~40 synthetic readers whose ratings follow taste clusters so the
collaborative filter has something to learn from.

Run manually:  python -m app.seed [--reset]
"""
import random
import sys
from datetime import date

from sqlalchemy import select

from . import config
from .database import Base, SessionLocal, engine
from .models import Author, Book, Genre, Publisher, Review, User, WishlistItem
from .moods import derive_mood_tags
from .schemas import BookIn
from .security import hash_password
from .services import apply_book_fields, get_or_create_named

DEMO_PASSWORD = "Password@123"

# (title, [authors], [genres], year, publisher, description)
BOOKS = [
    ("Introduction to Algorithms", ["Thomas H. Cormen", "Charles E. Leiserson", "Ronald L. Rivest", "Clifford Stein"], ["Computer Science", "Textbook"], 1990, "MIT Press",
     "The standard university text on algorithm design and analysis, covering sorting, graphs, dynamic programming and complexity."),
    ("Clean Code", ["Robert C. Martin"], ["Computer Science", "Programming"], 2008, "Prentice Hall",
     "Practical advice on writing readable, maintainable software through naming, small functions and disciplined refactoring."),
    ("The Pragmatic Programmer", ["Andrew Hunt", "David Thomas"], ["Computer Science", "Programming"], 1999, "Addison-Wesley",
     "Timeless tips for software craftspeople on tooling, debugging, automation and taking responsibility for your code."),
    ("Artificial Intelligence: A Modern Approach", ["Stuart Russell", "Peter Norvig"], ["Computer Science", "Artificial Intelligence", "Textbook"], 1995, "Prentice Hall",
     "A broad introduction to intelligent agents, search, knowledge, learning and probabilistic reasoning."),
    ("Database System Concepts", ["Abraham Silberschatz", "Henry F. Korth", "S. Sudarshan"], ["Computer Science", "Textbook"], 1986, None,
     "Core database theory: relational model, SQL, normalization, transactions and storage structures."),
    ("Python Crash Course", ["Eric Matthes"], ["Computer Science", "Programming"], 2015, "No Starch Press",
     "A hands-on, project-based introduction to Python programming for beginners."),
    ("Fluent Python", ["Luciano Ramalho"], ["Computer Science", "Programming"], 2015, "O'Reilly Media",
     "A deep dive into idiomatic Python features, data model, iterators, decorators and concurrency."),
    ("Designing Data-Intensive Applications", ["Martin Kleppmann"], ["Computer Science", "Textbook"], 2017, "O'Reilly Media",
     "Explains the principles behind reliable, scalable databases, streams, replication and distributed systems."),
    ("Discrete Mathematics and Its Applications", ["Kenneth H. Rosen"], ["Mathematics", "Textbook"], 1984, None,
     "Logic, sets, combinatorics, graphs and proofs presented for computer science students."),
    ("A Brief History of Time", ["Stephen Hawking"], ["Science", "Non-Fiction"], 1988, "Bantam Books",
     "An accessible tour of black holes, the Big Bang and the nature of space and time."),
    ("Cosmos", ["Carl Sagan"], ["Science", "Non-Fiction"], 1980, "Random House",
     "A lyrical journey through the universe and humanity's attempts to understand it."),
    ("The Selfish Gene", ["Richard Dawkins"], ["Science", "Non-Fiction"], 1976, None,
     "Presents evolution from the gene's point of view and introduced the idea of the meme."),
    ("Sapiens", ["Yuval Noah Harari"], ["History", "Non-Fiction"], 2011, None,
     "A sweeping history of humankind from the cognitive revolution to the modern age."),
    ("Thinking, Fast and Slow", ["Daniel Kahneman"], ["Psychology", "Non-Fiction"], 2011, "Farrar, Straus and Giroux",
     "Explores the two systems of thought that drive judgement, bias and decision making."),
    ("Atomic Habits", ["James Clear"], ["Self-Help", "Psychology"], 2018, "Avery",
     "A practical framework for building good habits and breaking bad ones through tiny daily changes."),
    ("Deep Work", ["Cal Newport"], ["Self-Help", "Business"], 2016, None,
     "Argues that focused, distraction-free work is a rare and valuable skill and shows how to cultivate it."),
    ("Man's Search for Meaning", ["Viktor E. Frankl"], ["Psychology", "Biography", "Philosophy"], 1946, None,
     "A psychiatrist's memoir of surviving concentration camps and his theory that purpose sustains life."),
    ("The Lean Startup", ["Eric Ries"], ["Business", "Non-Fiction"], 2011, None,
     "Introduces build-measure-learn loops for launching products under extreme uncertainty."),
    ("Rich Dad Poor Dad", ["Robert T. Kiyosaki"], ["Business", "Self-Help"], 1997, None,
     "Contrasts two attitudes toward money and promotes financial literacy and investing."),
    ("Steve Jobs", ["Walter Isaacson"], ["Biography", "Business"], 2011, None,
     "An authorised biography of Apple's co-founder drawn from dozens of interviews."),
    ("Educated", ["Tara Westover"], ["Biography", "Non-Fiction"], 2018, None,
     "A memoir of growing up in an isolated family and finding freedom through education."),
    ("Wings of Fire", ["A. P. J. Abdul Kalam", "Arun Tiwari"], ["Biography", "Science"], 1999, None,
     "The autobiography of India's Missile Man, from a small town in Tamil Nadu to the presidency."),
    ("Outliers", ["Malcolm Gladwell"], ["Psychology", "Non-Fiction"], 2008, None,
     "Examines the hidden factors, from timing to practice, behind extraordinary success."),
    ("The Alchemist", ["Paulo Coelho"], ["Fiction", "Philosophy"], 1988, None,
     "A shepherd boy travels from Spain to Egypt in search of treasure and his personal legend."),
    ("1984", ["George Orwell"], ["Classic", "Dystopian", "Science Fiction"], 1949, "Secker & Warburg",
     "A chilling vision of totalitarian surveillance, propaganda and the erasure of truth."),
    ("Pride and Prejudice", ["Jane Austen"], ["Classic", "Romance"], 1813, None,
     "Elizabeth Bennet and Mr Darcy navigate class, manners and misjudgement in Regency England."),
    ("To Kill a Mockingbird", ["Harper Lee"], ["Classic", "Fiction"], 1960, "J. B. Lippincott & Co.",
     "A young girl in the American South watches her lawyer father defend a wrongly accused man."),
    ("The Great Gatsby", ["F. Scott Fitzgerald"], ["Classic", "Fiction"], 1925, "Charles Scribner's Sons",
     "A mysterious millionaire's obsessive pursuit of lost love in Jazz Age New York."),
    ("The God of Small Things", ["Arundhati Roy"], ["Fiction", "Historical Fiction"], 1997, None,
     "Twins in Kerala live with the consequences of a forbidden love and a family tragedy."),
    ("Midnight's Children", ["Salman Rushdie"], ["Fiction", "Historical Fiction"], 1981, None,
     "A child born at the moment of India's independence is magically linked to the nation's destiny."),
    ("The Kite Runner", ["Khaled Hosseini"], ["Fiction", "Historical Fiction"], 2003, None,
     "An Afghan boy's betrayal of his friend haunts him across decades and continents."),
    ("The Book Thief", ["Markus Zusak"], ["Historical Fiction", "Young Adult"], 2005, None,
     "Narrated by Death, the story of a girl who steals books in Nazi Germany."),
    ("Dune", ["Frank Herbert"], ["Science Fiction", "Fantasy"], 1965, "Chilton Books",
     "A noble family fights for control of the desert planet that produces the universe's most valuable spice."),
    ("Foundation", ["Isaac Asimov"], ["Science Fiction"], 1951, "Gnome Press",
     "A mathematician predicts the fall of a galactic empire and creates a plan to shorten the dark age."),
    ("Neuromancer", ["William Gibson"], ["Science Fiction", "Thriller"], 1984, "Ace",
     "A washed-up hacker is hired for one last job in the neon-lit cyberspace of the future."),
    ("The Hobbit", ["J. R. R. Tolkien"], ["Fantasy", "Classic"], 1937, "George Allen & Unwin",
     "Bilbo Baggins joins a company of dwarves to reclaim their mountain home from a dragon."),
    ("Harry Potter and the Philosopher's Stone", ["J. K. Rowling"], ["Fantasy", "Young Adult"], 1997, "Bloomsbury",
     "An orphan discovers he is a wizard and begins his first year at a school of magic."),
    ("A Game of Thrones", ["George R. R. Martin"], ["Fantasy"], 1996, None,
     "Noble houses scheme for the Iron Throne while an ancient threat gathers in the north."),
    ("The Name of the Wind", ["Patrick Rothfuss"], ["Fantasy"], 2007, None,
     "A legendary wizard recounts his youth as a gifted orphan, musician and student of magic."),
    ("The Hunger Games", ["Suzanne Collins"], ["Young Adult", "Science Fiction", "Thriller"], 2008, None,
     "In a dystopian nation, a teenage girl volunteers for a televised fight to the death."),
    ("The Fault in Our Stars", ["John Green"], ["Young Adult", "Romance"], 2012, None,
     "Two teenagers meet in a cancer support group and fall in love."),
    ("Gone Girl", ["Gillian Flynn"], ["Thriller", "Mystery"], 2012, None,
     "On their anniversary a wife vanishes, and her husband becomes the prime suspect."),
    ("The Girl with the Dragon Tattoo", ["Stieg Larsson"], ["Mystery", "Thriller"], 2005, None,
     "A journalist and a gifted hacker investigate a decades-old disappearance in a powerful Swedish family."),
    ("Murder on the Orient Express", ["Agatha Christie"], ["Mystery", "Classic"], 1934, None,
     "Detective Hercule Poirot must solve a murder aboard a snowbound luxury train."),
    ("And Then There Were None", ["Agatha Christie"], ["Mystery", "Classic", "Thriller"], 1939, None,
     "Ten strangers on an island are killed one by one according to a nursery rhyme."),
    ("The Hound of the Baskervilles", ["Arthur Conan Doyle"], ["Mystery", "Classic"], 1902, None,
     "Sherlock Holmes investigates a spectral hound haunting an English moor."),
    ("The Da Vinci Code", ["Dan Brown"], ["Thriller", "Mystery"], 2003, None,
     "A symbologist races through Paris and London to decode a secret hidden in famous art."),
    ("It", ["Stephen King"], ["Horror", "Thriller"], 1986, None,
     "A group of childhood friends reunite to fight a shape-shifting evil in their hometown."),
    ("Dracula", ["Bram Stoker"], ["Horror", "Classic"], 1897, "Archibald Constable and Company",
     "Told through letters and diaries, a band of friends hunts the Transylvanian vampire count."),
    ("Frankenstein", ["Mary Shelley"], ["Horror", "Classic", "Science Fiction"], 1818, None,
     "A scientist's creation of artificial life leads to tragedy and moral reckoning."),
]

# Extra catalogue facts for the seeded titles (ISBN-13, approximate page count). Covers come from the Open Library
# Covers API by ISBN (`default=false` -> HTTP 404 when no cover exists, which the UI turns into a designed fallback).
# NOTE: the ISBNs are published edition ISBNs entered from reference; they cannot be verified offline.
CATALOG_EXTRAS = {
    'Introduction to Algorithms': {'isbn': '9780262033848', 'page_count': 1312, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780262033848-L.jpg?default=false'},
    'Clean Code': {'isbn': '9780132350884', 'page_count': 464, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780132350884-L.jpg?default=false'},
    'The Pragmatic Programmer': {'isbn': '9780201616224', 'page_count': 352, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780201616224-L.jpg?default=false'},
    'Artificial Intelligence: A Modern Approach': {'isbn': '9780136042594', 'page_count': 1152, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780136042594-L.jpg?default=false'},
    'Database System Concepts': {'isbn': '9780073523323', 'page_count': 1376, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780073523323-L.jpg?default=false'},
    'Python Crash Course': {'isbn': '9781593279288', 'page_count': 544, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9781593279288-L.jpg?default=false'},
    'Fluent Python': {'isbn': '9781491946008', 'page_count': 792, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9781491946008-L.jpg?default=false'},
    'Designing Data-Intensive Applications': {'isbn': '9781449373320', 'page_count': 616, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9781449373320-L.jpg?default=false'},
    'Discrete Mathematics and Its Applications': {'isbn': '9780073383095', 'page_count': 1072, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780073383095-L.jpg?default=false'},
    'A Brief History of Time': {'isbn': '9780553380163', 'page_count': 212, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780553380163-L.jpg?default=false'},
    'Cosmos': {'isbn': '9780345539434', 'page_count': 396, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780345539434-L.jpg?default=false'},
    'The Selfish Gene': {'isbn': '9780199291151', 'page_count': 360, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780199291151-L.jpg?default=false'},
    'Sapiens': {'isbn': '9780062316097', 'page_count': 464, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780062316097-L.jpg?default=false'},
    'Thinking, Fast and Slow': {'isbn': '9780374533557', 'page_count': 499, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780374533557-L.jpg?default=false'},
    'Atomic Habits': {'isbn': '9780735211292', 'page_count': 320, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780735211292-L.jpg?default=false'},
    'Deep Work': {'isbn': '9781455586691', 'page_count': 304, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9781455586691-L.jpg?default=false'},
    "Man's Search for Meaning": {'isbn': '9780807014295', 'page_count': 165, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780807014295-L.jpg?default=false'},
    'The Lean Startup': {'isbn': '9780307887894', 'page_count': 336, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780307887894-L.jpg?default=false'},
    'Rich Dad Poor Dad': {'isbn': '9781612680194', 'page_count': 336, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9781612680194-L.jpg?default=false'},
    'Steve Jobs': {'isbn': '9781451648539', 'page_count': 656, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9781451648539-L.jpg?default=false'},
    'Educated': {'isbn': '9780399590504', 'page_count': 352, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780399590504-L.jpg?default=false'},
    'Wings of Fire': {'isbn': '9788173711466', 'page_count': 180, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9788173711466-L.jpg?default=false'},
    'Outliers': {'isbn': '9780316017930', 'page_count': 320, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780316017930-L.jpg?default=false'},
    'The Alchemist': {'isbn': '9780062315007', 'page_count': 208, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780062315007-L.jpg?default=false'},
    '1984': {'isbn': '9780451524935', 'page_count': 328, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780451524935-L.jpg?default=false'},
    'Pride and Prejudice': {'isbn': '9780141439518', 'page_count': 432, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780141439518-L.jpg?default=false'},
    'To Kill a Mockingbird': {'isbn': '9780061120084', 'page_count': 336, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780061120084-L.jpg?default=false'},
    'The Great Gatsby': {'isbn': '9780743273565', 'page_count': 180, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780743273565-L.jpg?default=false'},
    'The God of Small Things': {'isbn': '9780679457312', 'page_count': 340, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780679457312-L.jpg?default=false'},
    "Midnight's Children": {'isbn': '9780812976533', 'page_count': 647, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780812976533-L.jpg?default=false'},
    'The Kite Runner': {'isbn': '9781594631931', 'page_count': 371, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9781594631931-L.jpg?default=false'},
    'The Book Thief': {'isbn': '9780375842207', 'page_count': 552, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780375842207-L.jpg?default=false'},
    'Dune': {'isbn': '9780441172719', 'page_count': 612, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780441172719-L.jpg?default=false'},
    'Foundation': {'isbn': '9780553293357', 'page_count': 255, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780553293357-L.jpg?default=false'},
    'Neuromancer': {'isbn': '9780441569595', 'page_count': 271, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780441569595-L.jpg?default=false'},
    'The Hobbit': {'isbn': '9780547928227', 'page_count': 310, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780547928227-L.jpg?default=false'},
    "Harry Potter and the Philosopher's Stone": {'isbn': '9780590353427', 'page_count': 309, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780590353427-L.jpg?default=false'},
    'A Game of Thrones': {'isbn': '9780553593716', 'page_count': 694, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780553593716-L.jpg?default=false'},
    'The Name of the Wind': {'isbn': '9780756404741', 'page_count': 662, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780756404741-L.jpg?default=false'},
    'The Hunger Games': {'isbn': '9780439023528', 'page_count': 374, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780439023528-L.jpg?default=false'},
    'The Fault in Our Stars': {'isbn': '9780525478812', 'page_count': 313, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780525478812-L.jpg?default=false'},
    'Gone Girl': {'isbn': '9780307588371', 'page_count': 422, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780307588371-L.jpg?default=false'},
    'The Girl with the Dragon Tattoo': {'isbn': '9780307454546', 'page_count': 465, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780307454546-L.jpg?default=false'},
    'Murder on the Orient Express': {'isbn': '9780062693662', 'page_count': 256, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780062693662-L.jpg?default=false'},
    'And Then There Were None': {'isbn': '9780062073488', 'page_count': 272, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780062073488-L.jpg?default=false'},
    'The Hound of the Baskervilles': {'isbn': '9780486282145', 'page_count': 256, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780486282145-L.jpg?default=false'},
    'The Da Vinci Code': {'isbn': '9780307474278', 'page_count': 489, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780307474278-L.jpg?default=false'},
    'It': {'isbn': '9781501142970', 'page_count': 1138, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9781501142970-L.jpg?default=false'},
    'Dracula': {'isbn': '9780486411095', 'page_count': 418, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780486411095-L.jpg?default=false'},
    'Frankenstein': {'isbn': '9780486282114', 'page_count': 280, 'cover_url': 'https://covers.openlibrary.org/b/isbn/9780486282114-L.jpg?default=false'},
}

# taste clusters used to generate realistic synthetic ratings
CLUSTERS = {
    "scifi_fantasy": {"Science Fiction", "Fantasy", "Young Adult", "Dystopian"},
    "mystery_thriller": {"Mystery", "Thriller", "Horror"},
    "classics_literary": {"Classic", "Fiction", "Historical Fiction", "Romance"},
    "tech_academic": {"Computer Science", "Programming", "Textbook", "Mathematics", "Artificial Intelligence"},
    "nonfiction_growth": {"Self-Help", "Business", "Psychology", "Biography", "Non-Fiction", "Science", "History"},
}

# (name, email, role, born, city, favourite genres, cluster)
PERSONAS = [
    ("Emma Carter", "emma@example.com", "reader", date(1999, 5, 14), "Rajkot", ["Romance", "Young Adult"], "classics_literary"),
    ("John Mehta", "john@example.com", "reader", date(1990, 3, 2), "Ahmedabad", ["Science Fiction", "Fantasy", "Thriller"], "scifi_fantasy"),
    ("Sarah Patel", "sarah@example.com", "reader", date(1985, 11, 23), "Surat", ["Classic", "Historical Fiction"], "classics_literary"),
    ("Alex Shah", "alex@example.com", "reader", date(2003, 8, 9), "Rajkot", [], None),  # brand-new reader: cold start
    ("Lucy Joshi", "lucy@example.com", "reader", date(1996, 1, 30), "Vadodara", ["Science Fiction", "Fantasy"], "scifi_fantasy"),
    ("Prof. Rao", "prof.rao@example.com", "professor", date(1974, 7, 19), "Rajkot", ["Computer Science", "Mathematics"], "tech_academic"),
    ("Meera Desai", "meera@example.com", "student", date(2004, 2, 11), "Rajkot", ["Computer Science", "Self-Help"], "tech_academic"),
]
COMMENTS_GOOD = ["Loved it — couldn't put it down.", "Brilliantly written and thought provoking.", "A must read, highly recommended.",
                 "Great pacing and memorable characters.", "Clear, useful and well structured."]
COMMENTS_BAD = ["Not for me, I struggled to finish it.", "Overhyped, found it slow.", "Interesting idea but poorly executed."]


def _rate(rng: random.Random, books: list[Book], user: User, cluster: str | None, n: int, db) -> None:
    """~75% of a user's reads come from their taste cluster (rated high), the rest are exploratory (rated low-mid)."""
    liked_genres = CLUSTERS.get(cluster, set())
    inside = [b for b in books if {g.name for g in b.genres} & liked_genres]
    outside = [b for b in books if b not in inside]
    n_in = min(len(inside), round(n * 0.75))
    pool = rng.sample(inside, n_in) + rng.sample(outside, min(len(outside), n - n_in))
    for b in pool:
        rating = rng.choice([4, 5, 5, 4, 3]) if b in inside else rng.choice([1, 2, 2, 3, 3])
        comment = None
        if rng.random() < 0.35:
            comment = rng.choice(COMMENTS_GOOD if rating >= 4 else COMMENTS_BAD)
        db.add(Review(user_id=user.id, book_id=b.id, rating=rating, comment=comment))


def seed(db, with_demo_users: bool = True) -> None:
    if db.scalar(select(Book.id).limit(1)):
        return
    for title, authors, genres, year, publisher, desc in BOOKS:
        b = Book()
        extra = CATALOG_EXTRAS.get(title, {})
        apply_book_fields(db, b, BookIn(title=title, authors=authors, genres=genres, publication_year=year,
                                        publisher=publisher, description=desc, isbn=extra.get("isbn"),
                                        cover_url=extra.get("cover_url"), page_count=extra.get("page_count")))
        db.add(b)
    db.flush()

    if not db.scalar(select(User).where(User.email == config.ADMIN_EMAIL)):
        db.add(User(name="Administrator", email=config.ADMIN_EMAIL, role="admin",
                    password_hash=hash_password(config.ADMIN_PASSWORD)))
    db.commit()
    if not with_demo_users:
        return

    rng = random.Random(42)  # deterministic demo data
    books = list(db.scalars(select(Book)))
    shared_hash = hash_password(DEMO_PASSWORD)  # hash once; all demo accounts share the demo password
    for name, email, role, dob, city, favs, cluster in PERSONAS:
        u = User(name=name, email=email, role=role, date_of_birth=dob, city=city, state="Gujarat", password_hash=shared_hash)
        u.favorite_genres = [get_or_create_named(db, Genre, g) for g in favs]
        db.add(u)
        db.flush()
        if cluster:
            _rate(rng, books, u, cluster, rng.randint(9, 14), db)
    # Alex (new reader) has no ratings and no preferences -> exercises the cold-start (popularity) path.
    # Give a couple of other personas a wishlist so that feature has demo data too.
    for email, titles in {"emma@example.com": ["The Fault in Our Stars"], "john@example.com": ["Dune"]}.items():
        pu = db.scalar(select(User).where(User.email == email))
        for t in titles:
            bk = next(b for b in books if b.title == t)
            if not db.get(Review, (pu.id, bk.id)):
                db.add(WishlistItem(user_id=pu.id, book_id=bk.id))

    first = ["Aarav", "Diya", "Kabir", "Isha", "Rohan", "Anaya", "Vihaan", "Meher", "Arjun", "Tara", "Neel", "Riya", "Yash", "Sana", "Dev"]
    last = ["Sharma", "Verma", "Trivedi", "Bhatt", "Gandhi", "Pandya", "Kapoor", "Nair", "Iyer", "Singh"]
    clusters = list(CLUSTERS)
    for i in range(40):
        cluster = clusters[i % len(clusters)]
        u = User(name=f"{rng.choice(first)} {rng.choice(last)}", email=f"reader{i + 1}@example.com",
                 role=rng.choice(["reader", "student", "student", "professor"]), password_hash=shared_hash,
                 date_of_birth=date(rng.randint(1970, 2005), rng.randint(1, 12), rng.randint(1, 28)))
        db.add(u)
        db.flush()
        _rate(rng, books, u, cluster, rng.randint(10, 18), db)
    db.commit()
    from .migrations import backfill  # reviews + wishlist -> feedback rows
    backfill(db)


def main() -> None:
    if "--reset" in sys.argv:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
        print(f"Seeded: {db.query(Book).count()} books, {db.query(User).count()} users, {db.query(Review).count()} reviews")
    print(f"Admin login : {config.ADMIN_EMAIL} / {config.ADMIN_PASSWORD}")
    print(f"Demo readers: emma@example.com, john@example.com, ... / {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
