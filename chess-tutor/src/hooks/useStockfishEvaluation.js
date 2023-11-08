import axios from "axios";

import { useQuery } from "@tanstack/react-query";

const useStockfishEvaluation = (fen) => {

  console.log("Fen:", fen)


  return useQuery({
    queryKey: ["stockfishEvaluation", fen],
    queryFn: async () => {
      const response = await axios.get(
        "https://stockfish.online/api/stockfish.php",
        {
          params: {
            fen: fen,
            depth: 10,
            //mode: "eval",
            mode: "bestmove"
          },
        }
      );
      if (response.data && response.data.success) {
        return response.data.data;
      } else {
        throw new Error("Error getting evaluation");
      }
    },
    enabled: !!fen, // This query will not automatically run until a fen is provided
  });
};

export default useStockfishEvaluation;
