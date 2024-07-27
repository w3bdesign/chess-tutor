import axios from "axios";
import { useQuery } from "@tanstack/react-query";

const useStockfishEvaluation = (fen) => {
  const fetchChessApi = async (fen) => {
    const response = await axios.post(
      "https://chess-api.com/v1",
      {
        fen: fen,
        depth: 13,
      },
      {
        headers: {
          "Content-Type": "application/json",
        },
      }
    );

    if (response.data) {
      return {
        evaluation: response.data.eval,
        mate: response.data.mate,
        bestMove: response.data.move,
        continuation: response.data.continuationArr,
      };
    } else {
      throw new Error("Error getting evaluation from Chess API");
    }
  };

  const { data, isLoading, error } = useQuery({
    queryKey: ["stockfishEvaluation", fen],
    queryFn: () => fetchChessApi(fen),
    enabled: !!fen,
  });

  return {
    data,
    isLoading,
    error,
  };
};

export default useStockfishEvaluation;
