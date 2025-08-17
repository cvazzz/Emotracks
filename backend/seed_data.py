from backend.app.db import init_db, session_scope
from backend.app.models import Response, ResponseStatus


def main():
    init_db()
    with session_scope() as s:
        if s.query(Response).count() == 0:
            s.add(Response(child_name="Ana", emotion="Feliz", status=ResponseStatus.COMPLETED))
            s.add(Response(child_name="Luis", emotion="Triste", status=ResponseStatus.COMPLETED))
            print("Seeded 2 responses.")
        else:
            print("Responses already exist; skipping.")


if __name__ == "__main__":
    main()
