import json
import sqlite3
from pathlib import Path

import streamlit as st

ARCHIVE_DB = Path("questionnaire_archive.db")


def get_archive_rows():
    if not ARCHIVE_DB.exists():
        return []

    conn = sqlite3.connect(ARCHIVE_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, user_id, year, month, date, time, questionnaire, responses, completed_at FROM completed_questionnaires ORDER BY completed_at DESC"
    )
    rows = cursor.fetchall()
    conn.close()

    result = []
    for row in rows:
        responses = []
        try:
            responses = json.loads(row["responses"])
        except Exception:
            responses = row["responses"]

        result.append(
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "date": f"{row['year']}-{row['month']:02d}-{row['date']:02d}",
                "time": row["time"],
                "questionnaire": row["questionnaire"],
                "responses": responses,
                "completed_at": row["completed_at"],
            }
        )
    return result


def main():
    st.set_page_config(page_title="Questionnaire Archive", layout="wide")
    st.title("Mental Health Questionnaire Archive")
    st.markdown(
        "This dashboard shows completed PHQ-9, GAD7, and PHQ4 questionnaires stored in the archive database."
    )

    if st.button("Refresh"):
        st.experimental_rerun()

    rows = get_archive_rows()
    st.write(f"Total completed questionnaires: {len(rows)}")

    if not rows:
        st.info("No archived questionnaire completions found yet.")
        return

    for row in rows[:50]:
        with st.expander(f"{row['completed_at']} — {row['user_id']} — {row['questionnaire']}"):
            st.write(
                {
                    "ID": row["id"],
                    "User": row["user_id"],
                    "Questionnaire": row["questionnaire"],
                    "Completed At": row["completed_at"],
                    "Date": row["date"],
                    "Time": row["time"],
                }
            )
            st.json(row["responses"])

    st.markdown("---")
    st.write("Showing the most recent 50 archived questionnaire completions.")


if __name__ == "__main__":
    main()
