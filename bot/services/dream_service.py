from bot.services.db_service import get_connection


def create_dream(telegram_id, title):
    conn = get_connection()
    cursor = conn.cursor()

    # ищем пользователя
    cursor.execute(
        "SELECT id FROM users WHERE telegram_id=?",
        (telegram_id,)
    )

    user = cursor.fetchone()

    # если пользователя нет — создаем
    if not user:
        cursor.execute(
            "INSERT INTO users (telegram_id) VALUES (?)",
            (telegram_id,)
        )
        conn.commit()

        cursor.execute(
            "SELECT id FROM users WHERE telegram_id=?",
            (telegram_id,)
        )

        user = cursor.fetchone()

    user_id = user[0]

    cursor.execute("""
    INSERT INTO dreams (user_id, title)
    VALUES (?, ?)
    """, (user_id, title))

    conn.commit()
    conn.close()


def get_user_dreams(telegram_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT dreams.id, dreams.title, dreams.progress
    FROM dreams
    JOIN users ON users.id = dreams.user_id
    WHERE users.telegram_id=?
    ORDER BY dreams.id DESC
    """, (telegram_id,))

    dreams = cursor.fetchall()

    conn.close()

    return dreams
