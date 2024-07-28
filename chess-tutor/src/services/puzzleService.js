// File: src/services/puzzleService.js

import axios from "axios";
import { Chess } from "chess.js";

const isDevelopment = import.meta.env.MODE === "development";

const fetchPuzzleFromAPI = async () => {
  const response = await axios.get("/api/chess-puzzle");
  return response.data;
};

const fetchPuzzleDirectly = async () => {
  const options = {
    method: "GET",
    url: "https://chess-puzzles.p.rapidapi.com/",
    params: {
      themes: '["middlegame","advantage"]',
      rating: "1500",
      themesType: "ALL",
      playerMoves: "4",
      count: "1",
    },
    headers: {
      "x-rapidapi-key": import.meta.env.VITE_RAPID_API_KEY,
      "x-rapidapi-host": "chess-puzzles.p.rapidapi.com",
    },
  };

  const response = await axios.request(options);
  return response.data.puzzles[0];
};

export const fetchPuzzle = async () => {
  try {
    const puzzleData = isDevelopment
      ? await fetchPuzzleDirectly()
      : await fetchPuzzleFromAPI();

    // Create a new Chess instance
    const chess = new Chess();
    chess.load(puzzleData.fen);

    return {
      id: puzzleData.puzzleid,
      fen: puzzleData.fen,
      solution: puzzleData.moves,
      rating: puzzleData.rating,
      themes: puzzleData.themes,
    };
  } catch (error) {
    console.error("Error fetching puzzle:", error);
    throw error;
  }
};
