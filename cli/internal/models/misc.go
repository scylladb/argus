package models

// Version contains version control commit id
type Version struct {
	CommitId string `json:"commit_id"`
}

func (Version) Headers() []string {
	return []string{"Commit Id"}
}

func (v Version) Rows() [][]string {
	return [][]string{{v.CommitId}}
}

// UserTokenResponse is the payload of GET /api/v1/user/token.
type UserTokenResponse struct {
	Token string `json:"token"`
}
