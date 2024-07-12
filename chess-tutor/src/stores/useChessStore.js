import { create } from "zustand";
import { Chess } from "chess.js";

const useChessStore = create((set, get) => ({
  chess: new Chess(),
  moveHistory: [],
  warningMessage: null,
  evaluationData: null,
  isLoading: false,
  error: null,

  makeMove: (from, to) => {
    const { chess } = get();
    try {
      const move = chess.move({ from, to, promotion: "q" });
      if (move === null) {
        const piece = chess.get(from);
        if (!piece) {
          set({ warningMessage: "No piece at the starting square." });
        } else if (chess.get(to) && piece.color === chess.get(to).color) {
          set({ warningMessage: "Cannot capture your own piece." });
        } else {
          set({
            warningMessage: `Invalid move for ${piece.type}. Please try again.`,
          });
        }
        return false;
      }
      set({
        moveHistory: chess.history({ verbose: true }),
        warningMessage: null,
      });
      return true;
    } catch (error) {
      console.error("Error making move:", error);
      const errorMessage = error.message.includes("Invalid move")
        ? "This move is not allowed. Please try a different move."
        : "An unexpected error occurred. Please try again.";
      set({ warningMessage: errorMessage });
      return false;
    }
  },

  setEvaluationData: (data) => set({ evaluationData: data }),
  setIsLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),

  resetGame: () => {
    const newChess = new Chess();
    set({
      chess: newChess,
      moveHistory: [],
      warningMessage: null,
      evaluationData: null,
      isLoading: false,
      error: null,
    });
  },
}));

export default useChessStore;
