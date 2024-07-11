import axios from "axios";
import { useQuery } from "@tanstack/react-query";

const useStockfishEvaluation = (fen) => {
  const { data, isLoading, error } = useQuery({
    queryKey: ["stockfishEvaluation", fen],
    queryFn: async () => {
      const response = await axios.get(
        "https://stockfish.online/api/s/v2.php",
        {
          params: {
            fen: fen,
            depth: 10,
          },
        }
      );

      if (response.data && response.data.success) {
        return {
          evaluation: response.data.evaluation,
          mate: response.data.mate,
          bestMove: response.data.bestmove.split(" ")[1], // Extract the best move
          continuation: response.data.continuation,
        };
      } else {
        throw new Error("Error getting evaluation");
      }
    },
    enabled: !!fen, // This query will not automatically run until a fen is provided
  });

  return {
    data,
    isLoading,
    error,
  };
};

export default useStockfishEvaluation;
