int: n; % number of operations
int: m; % number of workstations
set of int: N = 1..n;

array[N, 1..m] of 0..1: W; % 1 if operation i ∈ workstation K
array[N, 1..m] of float: t; % processing time of operation i on workstation K
int: M; % large positive number
array[N] of var 0.0..M: S; % start time of operation i
array[N] of var 0.0..M: C; % completion time of operation i
array[N] of int: d; % the immediate downstream operation, or successor, of operation i
array[N, 1..m] of var 0..1: A; % A(w,i) = 1 if operation i is assigned to workstation w, 0 otherwise

constraint forall(i in N)(sum(w in 1..m)(A[i,w]) = 1); % each task is assigned to exactly one workstation
constraint forall(i in N)(sum(w in 1..m where W[i,w]=0)(A[i,w]) = 0); % the task cannot be assigned to non-eligible workstations
constraint forall(i in N, w in 1..m where A[i,w]=1)(C[i] = S[i] + t[i,w]);

constraint forall(i in N where d[i]!=-1)(S[d[i]] >= C[i]);
array[N,N] of var 0..1: delta; % 1 if operation j precedes i (i,j ∈ K,i ̸= j,1≤K≤m), 0 otherwise.
constraint forall(w in 1..m, i,j in N where i!=j /\ A[i,w]=1 /\ A[j,w]=1)(delta[i,j]+delta[j,i] = 1);
constraint forall(w in 1..m, i,j in N where i!=j /\ A[i,w]=1 /\ A[j,w]=1)(S[i]-C[j] >= M*(delta[i,j]-1));

int: E; % nr of final operations
array[1..E] of int: finalPosition; % ids of final operations
array[1..E] of float: D; % due date of final assembly

constraint forall(e in 1..E)(C[finalPosition[e]] <= D[e]);

var float: objective;
%constraint objective = sum(i in N)(S[i]);
%constraint objective = min(i in N)(S[i]);
%solve maximize objective;

constraint objective = max(e in 1..E)(C[finalPosition[e]]);
solve minimize objective;