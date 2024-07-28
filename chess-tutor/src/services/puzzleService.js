import axios from "axios";
import { Chess } from "chess.js";

export const fetchPuzzle = async () => {
  try {
    const response = await axios.get("/api/chess-puzzle");
    const puzzleData = response.data;

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
