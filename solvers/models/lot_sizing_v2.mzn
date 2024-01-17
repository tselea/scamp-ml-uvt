int: n; % number of operations
int: m; % number of workstations
set of int: N = 1..n;

array[N, 1..m] of 0..1: W; % 1 if operation i ∈ workstation K
array[N, 1..m] of float: t; % processing time of operation i on workstation K
int: M; % large positive number
array[N] of var 0.0..M: S; % start time of operation i
array[N] of var 0.0..M: C; % completion time of operation i
array[N] of int: d; % the immediate downstream operation, or successor, of operation i
array[N] of var 1..m: A; % A(i) = w if operation i is assigned to workstation w
array[N] of -1.0..M: R;

constraint forall(i in N)(W[i,A[i]] = 1);
constraint forall(i in N, w in 1..m where A[i]=w)(C[i] = S[i] + t[i,w]);

constraint forall(i in N where d[i]!=-1)(S[d[i]] >= C[i]);
constraint forall(w in 1..m, i,j in N where i!=j /\ A[i]=w /\ A[j]=w)(C[i] <= S[j] \/ S[i] >= C[j]);

int: E; % nr of final operations
array[1..E] of int: finalPosition; % ids of final operations
array[1..E] of float: D; % due date of final assembly

constraint forall(e in 1..E)(C[finalPosition[e]] <= D[e]);

constraint forall(i in N where R[i]!=-1)(S[i] = R[i]);

var float: objective;
%constraint objective = sum(i in N)(S[i]);
%constraint objective = min(i in N)(S[i]);
%solve maximize objective;

constraint objective = max(e in 1..E)(C[finalPosition[e]]);
solve minimize objective;