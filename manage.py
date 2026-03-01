import sys
from flask_migrate import init, migrate, upgrade, downgrade
from migrations_app import app

def print_usage():
    print("Usage:")
    print("python manage.py init")
    print("python manage.py migrate \"message\"")
    print("python manage.py upgrade")
    print("python manage.py downgrade")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    command = sys.argv[1]
    
    with app.app_context():
        if command == "init":
            init()
        elif command == "migrate":
            message = sys.argv[2] if len(sys.argv) > 2 else "migration"
            migrate(message=message)
        elif command == "upgrade":
            upgrade()
        elif command == "downgrade":
            downgrade()
        else:
            print_usage()
            sys.exit(1)