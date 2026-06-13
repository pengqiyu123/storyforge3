import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BookCard } from "./BookCard";

const book = {
  book_id: "lurenjia",
  title: "我是路人甲",
  genre: "urban",
  platform: "tomato",
  status: "active",
  target_chapters: 100,
  chapter_word_count: 2500,
  current_chapter: 3,
  created_at: "2026-06-08T00:00:00Z",
  updated_at: "2026-06-08T00:00:00Z"
};

describe("BookCard", () => {
  it("links to the book detail page", () => {
    render(
      <MemoryRouter>
        <BookCard book={book} />
      </MemoryRouter>
    );

    expect(screen.getByRole("link", { name: /我是路人甲/ })).toHaveAttribute("href", "/books/lurenjia");
  });
});
