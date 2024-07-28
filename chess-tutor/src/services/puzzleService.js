// https://rapidapi.com/KeeghanM/api/chess-puzzles/playground/apiendpoint_177d3683-dcc4-4a7b-812a-884e259e1304

import axios from 'axios';
import { Chess } from 'chess.js';

export const fetchPuzzle = async () => {
  try {
    const options = {
      method: 'GET',
      url: 'https://chess-puzzles.p.rapidapi.com/',
      params: {
        themes: '["middlegame","advantage"]',
        rating: '1500',
        themesType: 'ALL',
        playerMoves: '4',
        count: '1'
      },
      headers: {
        // TODO: Move this to /api endpoint
        'x-rapidapi-key': '',
        'x-rapidapi-host': 'chess-puzzles.p.rapidapi.com'
      }
    };

    const response = await axios.request(options);
    const puzzleData = response.data.puzzles[0];

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
    console.error('Error fetching puzzle:', error);
    throw error;
  }
};